#include "QueueActor.h"
#include "QueuingCharacter.h"
#include "NavMesh/NavMeshBoundsVolume.h"
#include "NavigationSystem.h"
#include "Components/BrushComponent.h"
#include "PhysicsEngine/BodySetup.h"
#include "Engine/World.h"
#include "UObject/ConstructorHelpers.h"

AQueueActor::AQueueActor()
{
	BaseMesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("BaseMesh"));
	BaseMesh->SetupAttachment(SceneComponent);

	static ConstructorHelpers::FObjectFinder<UStaticMesh> CubeMeshAsset(TEXT("/Engine/BasicShapes/Cube"));
	if (CubeMeshAsset.Succeeded())
	{
		BaseMesh->SetStaticMesh(CubeMeshAsset.Object);
	}

	BaseMesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	BaseMesh->SetRelativeScale3D(FVector(6.0f, 4.0f, 0.2f));
	BaseMesh->SetRelativeLocation(FVector(-250.0f, 0.0f, 10.0f));
}

void AQueueActor::BeginPlay()
{
	Super::BeginPlay();
}

void AQueueActor::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	GetWorldTimerManager().ClearTimer(CycleTimerHandle);
	GetWorldTimerManager().ClearTimer(NavMeshReadyTimerHandle);

	for (TWeakObjectPtr<AQueuingCharacter> Character : Characters)
	{
		if (Character.IsValid())
		{
			Character->Destroy();
		}
	}
	Characters.Empty();

	if (NavMeshBoundsVolume)
	{
		NavMeshBoundsVolume->Destroy();
		NavMeshBoundsVolume = nullptr;
	}

	Super::EndPlay(EndPlayReason);
}

void AQueueActor::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);

	for (int32 i = 0; i < Characters.Num(); ++i)
	{
		if (AQueuingCharacter* Character = Characters[i].Get())
		{
			if (Character->bIsMoving)
			{
				const float TimeSinceLastMove = GetWorld()->GetTimeSeconds() - Character->GetLastRenderTime();
				if (TimeSinceLastMove > MovementTimeout)
				{
					const FVector TargetPos = GetSlotWorldPosition(Character->CurrentSlotIndex);
					Character->SetActorLocation(TargetPos);
					Character->bIsMoving = false;
				}
			}
		}
	}
}

void AQueueActor::InitQueue(const FQueuingInfo& InQueuingInfo)
{
	QueuingInfo = InQueuingInfo;
	QueueDirection = FRotator(0.0, InQueuingInfo.Heading, 0.0);
	TargetPersonCount = InQueuingInfo.PersonCount;
	Spacing = InQueuingInfo.Spacing;

	SetActorLocation(QueuingInfo.Location);
	SetActorRotation(QueueDirection);

	CreateNavMeshBoundsVolume();

	GetWorldTimerManager().SetTimer(NavMeshReadyTimerHandle, this, &AQueueActor::OnNavMeshReady, 0.5f, false);
}

void AQueueActor::OnNavMeshReady()
{
	RebuildNavMesh();
	SpawnInitialCharacters();

	GetWorldTimerManager().SetTimer(CycleTimerHandle, this, &AQueueActor::AdvanceQueue, CycleInterval, true);
}

FVector AQueueActor::GetSlotWorldPosition(int32 SlotIndex) const
{
	const FVector ForwardVector = QueueDirection.Vector();
	return QueuingInfo.Location - ForwardVector * Spacing * SlotIndex;
}

AQueuingCharacter* AQueueActor::SpawnCharacterAtPosition(const FVector& WorldPosition, int32 SlotIndex)
{
	UWorld* World = GetWorld();
	if (!World) return nullptr;

	FActorSpawnParameters SpawnParams;
	SpawnParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;

	AQueuingCharacter* Character = World->SpawnActor<AQueuingCharacter>(AQueuingCharacter::StaticClass(),
		WorldPosition, QueueDirection, SpawnParams);
	if (Character)
	{
		Character->CurrentSlotIndex = SlotIndex;
		Character->OwningQueue = this;
		NextCharacterIndex++;
	}
	return Character;
}

void AQueueActor::SpawnInitialCharacters()
{
	for (int32 i = 0; i < TargetPersonCount; ++i)
	{
		const FVector SlotPos = GetSlotWorldPosition(i);
		if (AQueuingCharacter* Character = SpawnCharacterAtPosition(SlotPos, i))
		{
			Characters.Add(Character);
		}
	}
}

void AQueueActor::RemoveCharacterAtFront()
{
	if (Characters.Num() > 0)
	{
		if (AQueuingCharacter* FrontCharacter = Characters[0].Get())
		{
			FrontCharacter->Destroy();
		}
		Characters.RemoveAt(0);
	}
}

void AQueueActor::SpawnCharacterAtTail()
{
	const int32 TailSlot = TargetPersonCount - 1;
	const FVector TailPos = GetSlotWorldPosition(TailSlot);
	if (AQueuingCharacter* Character = SpawnCharacterAtPosition(TailPos, TailSlot))
	{
		Characters.Add(Character);
	}
}

void AQueueActor::AdvanceQueue()
{
	RemoveCharacterAtFront();

	for (int32 i = 0; i < Characters.Num(); ++i)
	{
		if (AQueuingCharacter* Character = Characters[i].Get())
		{
			Character->CurrentSlotIndex = i;
			const FVector TargetPos = GetSlotWorldPosition(i);
			Character->MoveToPosition(TargetPos);
		}
	}

	SpawnCharacterAtTail();
}

void AQueueActor::OnCharacterReachedDestination(AQueuingCharacter* Character) const
{
	if (Character && !Character->bIsMoving)
	{
		Character->SetActorRotation(QueueDirection);
	}
}

void AQueueActor::CreateNavMeshBoundsVolume()
{
	UWorld* World = GetWorld();
	if (!World) return;

	const FVector NavCenter = BaseMesh->GetComponentLocation();
	const FRotator NavRotation = BaseMesh->GetComponentRotation();

	const FVector BaseScale = BaseMesh->GetRelativeScale3D();
	const FVector BoundsSize(BaseScale.X * 100.0f, BaseScale.Y * 100.0f, BaseScale.Z * 100.0f);

	FActorSpawnParameters SpawnParams;
	SpawnParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	NavMeshBoundsVolume = World->SpawnActor<ANavMeshBoundsVolume>(
		ANavMeshBoundsVolume::StaticClass(), NavCenter, NavRotation, SpawnParams);

	if (NavMeshBoundsVolume)
	{
		if (UBrushComponent* BrushComp = NavMeshBoundsVolume->GetBrushComponent())
		{
			UBodySetup* BodySetup = NewObject<UBodySetup>(BrushComp);
			BodySetup->CollisionTraceFlag = CTF_UseSimpleAsComplex;

			FKBoxElem BoxElem;
			BoxElem.Center = FVector::ZeroVector;
			BoxElem.Rotation = FRotator::ZeroRotator;
			BoxElem.X = BoundsSize.X;
			BoxElem.Y = BoundsSize.Y;
			BoxElem.Z = BoundsSize.Z;
			BodySetup->AggGeom.BoxElems.Add(BoxElem);

			BrushComp->BrushBodySetup = BodySetup;
			BrushComp->MarkRenderStateDirty();
			BrushComp->UpdateNavigationBounds();
			BrushComp->RecreatePhysicsState();
		}
	}
}

void AQueueActor::RebuildNavMesh()
{
	UWorld* World = GetWorld();
	if (!World) return;

	if (UNavigationSystemV1* NavSys = FNavigationSystem::GetCurrent<UNavigationSystemV1>(World))
	{
		NavSys->Build();
	}
}

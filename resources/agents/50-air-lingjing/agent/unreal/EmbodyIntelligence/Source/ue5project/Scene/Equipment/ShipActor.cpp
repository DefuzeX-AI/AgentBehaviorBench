// Fill out your copyright notice in the Description page of Project Settings.

#include "ShipActor.h"
#include "Engine/StaticMesh.h"
#include "UObject/ConstructorHelpers.h"
#include "ue5project/Core/DataManager.h"
#include "ue5project/Scene/Task/Rescue/RescuePersonActor.h"
#include "ue5project/Scene/Task/TaskMatrixController.h"
#include "ue5project/Scene/Task/TaskPointActor.h"
#include "ue5project/Temp/BlueprintTempHelper.h"

AShipActor::AShipActor()
{
	PrimaryActorTick.bCanEverTick = true;


	SphereComp = CreateDefaultSubobject<USphereComponent>(TEXT("Sphere"));
	SphereComp->SetupAttachment(RootComponent);
	SphereComp->SetSphereRadius(13000.0f);
	SphereComp->SetCollisionProfileName(TEXT("OverlapAllDynamic"));
	SphereComp->SetGenerateOverlapEvents(true);
	SphereComp->CanCharacterStepUpOn = ECB_Yes;
	SphereComp->OnComponentBeginOverlap.AddDynamic(this, &AShipActor::OnSphereBeginOverlap);


	MeshComp = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("ShipMesh"));
	MeshComp->SetupAttachment(RootComponent);
	static ConstructorHelpers::FObjectFinder<UStaticMesh> ShipMeshAsset(
		TEXT("StaticMesh'/Game/ArtRes/Base_Art/Mesh/JST_1.JST_1'"));
	if (ShipMeshAsset.Succeeded())
	{
		MeshComp->SetStaticMesh(ShipMeshAsset.Object);
	}
}

void AShipActor::BeginPlay()
{
	Super::BeginPlay();
	SnapGround();
}

FSColor AShipActor::GetTagWidgetColor() const
{
	return FSColor(255, 0, 255, 0.5f);
}

FString AShipActor::GetImageSaveSubdir() const
{
	return TEXT("Ship");
}

void AShipActor::OnSphereBeginOverlap(UPrimitiveComponent* /*OverlappedComp*/, AActor* OtherActor,
                                      UPrimitiveComponent* /*OtherComp*/, int32 /*OtherBodyIndex*/,
                                      bool /*bFromSweep*/, const FHitResult& /*SweepResult*/)
{
	if (ARescuePersonActor* RescuePerson = Cast<ARescuePersonActor>(OtherActor))
	{
		OnRescuePeople(RescuePerson);   // RescuePersonActor IS-A ATaskPointActor
	}
}

void AShipActor::UpdateHeadingToTarget(const FVector2D& InDirection2D)
{
	if (InDirection2D.IsNearlyZero())
	{
		return;
	}

	const float TargetYaw = FMath::RadiansToDegrees(FMath::Atan2(InDirection2D.Y, InDirection2D.X));
	FRotator CurrentRotation = GetActorRotation();
	CurrentRotation.Yaw = TargetYaw;
	SetActorRotation(CurrentRotation);
}

void AShipActor::ExecuteEquipmentMoveTask2D(const FEquipmentMoveTask2D& InMoveTask2D)
{
	if (InMoveTask2D.TargetPositions.IsEmpty() || InMoveTask2D.Speed <= 0.0)
	{
		return;
	}


	MovePathPoints2D.Empty();
	const FVector CurrentLocation = GetActorLocation();
	const FVector2D CurrentPosition2D(CurrentLocation.X, CurrentLocation.Y);
	MovePathPoints2D.Add(CurrentPosition2D);
	MovePathPoints2D.Append(InMoveTask2D.TargetPositions);


	MoveSpeed2D = InMoveTask2D.Speed * 100.0;
	CurrentMoveTargetIndex2D = 1;
	bIsMoving2D = true;
	bRescuedThisMove2D = false;


	UpdateHeadingToTarget(MovePathPoints2D[1] - MovePathPoints2D[0]);


	TaskStartTime = FDateTime::Now().ToUnixTimestamp();
}

void AShipActor::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);

	if (!bIsMoving2D || MovePathPoints2D.Num() < 2 || CurrentMoveTargetIndex2D >= MovePathPoints2D.Num())
	{
		return;
	}

	const FVector2D& TargetPoint = MovePathPoints2D[CurrentMoveTargetIndex2D];
	FVector CurrentLocation = GetActorLocation();
	const FVector2D CurrentPosition2D(CurrentLocation.X, CurrentLocation.Y);

	const FVector2D Direction = TargetPoint - CurrentPosition2D;
	const double DistanceToTarget = Direction.Size();


	if (const double MoveDistance = MoveSpeed2D * DeltaTime;
		DistanceToTarget <= MoveDistance)
	{

		CurrentLocation.X = TargetPoint.X;
		CurrentLocation.Y = TargetPoint.Y;
		SetActorLocation(CurrentLocation);


		CurrentMoveTargetIndex2D++;
		if (CurrentMoveTargetIndex2D >= MovePathPoints2D.Num())
		{

			bIsMoving2D = false;

			if (!bRescuedThisMove2D)
			{
				SendRescueResult(false, FString());
			}
		}
		else
		{

			const FVector2D NextDirection = MovePathPoints2D[CurrentMoveTargetIndex2D] - MovePathPoints2D[CurrentMoveTargetIndex2D - 1];
			UpdateHeadingToTarget(NextDirection);
		}
	}
	else
	{

		const FVector2D NormalizedDirection = Direction / DistanceToTarget;
		const FVector2D NewPosition2D = CurrentPosition2D + NormalizedDirection * MoveDistance;
		CurrentLocation.X = NewPosition2D.X;
		CurrentLocation.Y = NewPosition2D.Y;
		SetActorLocation(CurrentLocation);
	}
}

void AShipActor::SendRescueResult(const bool bSucceed, const FString& InPersonId)
{
	if (const ADataManager* DataManager = FTempController::Get()->DataManager.Get())
	{
		const FVector ShipLocation = GetActorLocation();
		const int64 CurrentTimeStamp = FDateTime::Now().ToUnixTimestamp();



		const int32 DuringSeconds = TaskStartTime > 0 ? static_cast<int32>(CurrentTimeStamp - TaskStartTime) : 0;
		DataManager->SendShipRescueMessage(EquipmentInfo.EquipmentId, DuringSeconds, bSucceed, InPersonId, ShipLocation);
	}
}

void AShipActor::OnRescuePeople(const ATaskPointActor* InTaskPointActor)
{
	if (!InTaskPointActor)
	{
		return;
	}
	bRescuedThisMove2D = true;
	const FString&& TaskPointId = InTaskPointActor->GetTaskPointId();
	FTaskMatrixController::Get()->RemoveTaskPoint(TaskPointId);
	SendRescueResult(true, TaskPointId);
}

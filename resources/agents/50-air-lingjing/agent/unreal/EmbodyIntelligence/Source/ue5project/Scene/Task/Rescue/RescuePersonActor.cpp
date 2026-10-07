#include "RescuePersonActor.h"

#include "Components/SphereComponent.h"
#include "UObject/ConstructorHelpers.h"

ARescuePersonActor::ARescuePersonActor()
{
	ChildActorComponent = CreateDefaultSubobject<UChildActorComponent>(TEXT("ChildActorComponent"));
	ChildActorComponent->SetupAttachment(SceneComponent);
	static ConstructorHelpers::FClassFinder<AActor> ActorClassFinder(TEXT("/Script/Engine.Blueprint'/Game/ArtRes/Base_Art/BluePrint/RW_Water/BluePrint/BP_RW_Water_1.BP_RW_Water_1_C'"));
	if (ActorClassFinder.Succeeded())
	{
		ChildActorComponent->SetChildActorClass(ActorClassFinder.Class);
	}
	ChildActorComponent->SetRelativeScale3D(FVector(10.0));
	SphereComponent = CreateDefaultSubobject<USphereComponent>(TEXT("SphereComponent"));
	SphereComponent->SetupAttachment(ChildActorComponent);
	SphereComponent->SetSphereRadius(150.f);
	SphereComponent->SetRelativeLocation(FVector(60.0, 0.0, -50.f));
//	SphereComponent->SetHiddenInGame(false);
}

void ARescuePersonActor::BeginPlay()
{
	Super::BeginPlay();
}

void ARescuePersonActor::InitTaskPoint(const FTaskPointInfo& InTaskPointInfo)
{
	Super::InitTaskPoint(InTaskPointInfo);
	
	InitTagWidget(FSColor(255, 0, 0, 0.5f), TaskPointInfo.TaskPointId);
}

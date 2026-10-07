#include "PollutionActor.h"
#include "UObject/ConstructorHelpers.h"

APollutionActor::APollutionActor()
{
	ChildActorComponent = CreateDefaultSubobject<UChildActorComponent>(TEXT("ChildActorComponent"));
	ChildActorComponent->SetupAttachment(SceneComponent);
	static ConstructorHelpers::FClassFinder<AActor> ActorClassFinder(TEXT("/Script/Engine.Blueprint'/Game/ArtRes/Waterfalls/Meshes/BP_GuanDao.BP_GuanDao_C'"));
	if (ActorClassFinder.Succeeded())
	{
		ChildActorComponent->SetChildActorClass(ActorClassFinder.Class);
	}
}

void APollutionActor::InitTaskPoint(const FTaskPointInfo& InTaskPointInfo)
{
	Super::InitTaskPoint(InTaskPointInfo);
	
	InitTagWidget(FSColor(255, 0, 0, 0.5f), TaskPointInfo.TaskPointId);
}

void APollutionActor::BeginPlay()
{
	Super::BeginPlay();
	
}
